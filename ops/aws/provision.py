"""
Create the AWS resources Spark needs, and nothing else.

Every resource is created fresh and tagged ``Name=spark-api``. The script never
stops, restarts, modifies or deletes an existing instance, security group, IP
or DNS record. It looks resources up by that tag, so running it twice reuses
what it made the first time instead of building a second copy.

Two deliberate choices about the security group:

* Ports 80 and 443 are opened only to Cloudflare's published ranges. That stops
  anyone reaching the origin directly and bypassing the proxy.
* Port 22 is opened only to the public IP of the machine running this script.
  If your address changes, rerun with --refresh-ssh to add the new one.

Usage:
    python -m ops.aws.provision            # plan only
    python -m ops.aws.provision --apply
    python -m ops.aws.provision --refresh-ssh
"""

from __future__ import annotations

import argparse
import json
import subprocess
import urllib.request

REGION = "ap-south-1"
PROFILE = "aevrin"
VPC = "vpc-012b3640d45ffe783"
SUBNET = "subnet-03bcbeef9b349ff2f"          # ap-south-1a, public
AMI = "ami-050c78efa486a0196"                # Ubuntu 24.04 LTS, amd64, gp3
INSTANCE_TYPE = "t3.small"
KEY_NAME = "aevrin-api"
NAME = "spark-api"
SG_NAME = "spark-api-sg"
DISK_GB = 30


def aws(*args: str) -> object:
    """Run one AWS CLI call and parse its JSON, so failures are loud."""
    cmd = ["aws", *args, "--profile", PROFILE, "--region", REGION, "--output", "json"]
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"{' '.join(args[:2])} failed: {p.stderr.strip()[:400]}")
    return json.loads(p.stdout) if p.stdout.strip() else None


def my_ip() -> str:
    with urllib.request.urlopen("https://api.ipify.org", timeout=20) as r:
        return r.read().decode().strip()


def cloudflare_ranges() -> list[str]:
    with urllib.request.urlopen("https://api.cloudflare.com/client/v4/ips", timeout=20) as r:
        return json.loads(r.read().decode())["result"]["ipv4_cidrs"]


def find_sg() -> str | None:
    got = aws("ec2", "describe-security-groups",
              "--filters", f"Name=group-name,Values={SG_NAME}", f"Name=vpc-id,Values={VPC}",
              "--query", "SecurityGroups[].GroupId")
    return got[0] if got else None


def find_instance() -> dict | None:
    got = aws("ec2", "describe-instances",
              "--filters", f"Name=tag:Name,Values={NAME}",
              "Name=instance-state-name,Values=pending,running,stopping,stopped",
              "--query", "Reservations[].Instances[].{Id:InstanceId,State:State.Name,Ip:PublicIpAddress}")
    return got[0] if got else None


def find_eip() -> dict | None:
    got = aws("ec2", "describe-addresses", "--filters", f"Name=tag:Name,Values={NAME}",
              "--query", "Addresses[].{Ip:PublicIp,Alloc:AllocationId,Assoc:InstanceId}")
    return got[0] if got else None


def authorize(sg: str, port: int, cidr: str, note: str) -> None:
    try:
        aws("ec2", "authorize-security-group-ingress", "--group-id", sg,
            "--ip-permissions",
            json.dumps([{"IpProtocol": "tcp", "FromPort": port, "ToPort": port,
                         "IpRanges": [{"CidrIp": cidr, "Description": note}]}]))
    except RuntimeError as exc:
        if "Duplicate" not in str(exc):
            raise


def ensure_sg(apply: bool) -> str | None:
    sg = find_sg()
    if sg:
        print(f"security group   reuse {sg}")
        return sg
    print(f"security group   create {SG_NAME}")
    if not apply:
        return None
    sg = aws("ec2", "create-security-group", "--group-name", SG_NAME,
             "--description", "Spark API origin. HTTP from Cloudflare only.",
             "--vpc-id", VPC,
             "--tag-specifications",
             f"ResourceType=security-group,Tags=[{{Key=Name,Value={NAME}}}]")["GroupId"]
    for cidr in cloudflare_ranges():
        authorize(sg, 80, cidr, "Cloudflare")
        authorize(sg, 443, cidr, "Cloudflare")
    authorize(sg, 22, f"{my_ip()}/32", "admin")
    print(f"                 created {sg}, Cloudflare ranges plus your IP on 22")
    return sg


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--refresh-ssh", action="store_true")
    args = ap.parse_args()

    if args.refresh_ssh:
        sg = find_sg()
        if not sg:
            print("No Spark security group yet.")
            return 1
        ip = my_ip()
        authorize(sg, 22, f"{ip}/32", "admin")
        print(f"SSH allowed from {ip}/32 on {sg}")
        return 0

    print(f"region           {REGION}")
    print(f"account          {aws('sts', 'get-caller-identity')['Account']}")
    sg = ensure_sg(args.apply)

    inst = find_instance()
    if inst:
        print(f"instance         reuse {inst['Id']} ({inst['State']})")
    else:
        print(f"instance         create {INSTANCE_TYPE} from {AMI}")

    eip = find_eip()
    if eip:
        print(f"elastic ip       reuse {eip['Ip']}")
    else:
        print("elastic ip       allocate new")

    if not args.apply:
        print("\nPlan only. Nothing was created. Pass --apply to build it.")
        return 0

    if not inst:
        inst_id = aws(
            "ec2", "run-instances", "--image-id", AMI, "--instance-type", INSTANCE_TYPE,
            "--key-name", KEY_NAME, "--subnet-id", SUBNET, "--security-group-ids", sg,
            "--block-device-mappings",
            json.dumps([{"DeviceName": "/dev/sda1",
                         "Ebs": {"VolumeSize": DISK_GB, "VolumeType": "gp3",
                                 "DeleteOnTermination": True}}]),
            "--metadata-options", "HttpTokens=required",
            "--tag-specifications",
            f"ResourceType=instance,Tags=[{{Key=Name,Value={NAME}}},{{Key=Project,Value=spark}}]",
        )["Instances"][0]["InstanceId"]
        print(f"instance         launched {inst_id}")
        subprocess.run(["aws", "ec2", "wait", "instance-running", "--instance-ids", inst_id,
                        "--profile", PROFILE, "--region", REGION], check=True)
    else:
        inst_id = inst["Id"]

    if not eip:
        alloc = aws("ec2", "allocate-address", "--domain", "vpc",
                    "--tag-specifications",
                    f"ResourceType=elastic-ip,Tags=[{{Key=Name,Value={NAME}}}]")
        eip = {"Ip": alloc["PublicIp"], "Alloc": alloc["AllocationId"], "Assoc": None}
        print(f"elastic ip       allocated {eip['Ip']}")

    if eip.get("Assoc") != inst_id:
        aws("ec2", "associate-address", "--instance-id", inst_id,
            "--allocation-id", eip["Alloc"])
        print(f"elastic ip       associated with {inst_id}")

    print(f"\nSpark origin is {eip['Ip']} on instance {inst_id}")
    print("The Elastic IP survives stop/start, so DNS will not break.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
