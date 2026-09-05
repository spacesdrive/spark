"""
Operational scripts: provisioning, deployment, and the checks around them.

Every script here is run as a module from the project root, for example::

    python -m ops.site.build_docs
    python -m ops.aws.provision --apply

Running them that way is what lets them share :mod:`ops.paths`, and it means
none of them has to guess where the project root is from its own depth.
"""
