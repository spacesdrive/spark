/**
 * The route table.
 *
 * Every route in the sidebar resolves to a real page. There is no route that
 * renders a placeholder, and no sidebar entry without a route.
 *
 * The overview is imported directly because it is the landing page. Everything
 * else loads on demand, so the first paint stays small.
 */

import { lazy } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { Link } from "react-router-dom";
import { Button, Card, EmptyState } from "@/components/ui/primitives";
import { Icon } from "@/components/ui/icons";
import { Overview } from "@/pages/Overview";

const TestTransaction = lazy(() =>
  import("@/pages/TestTransaction").then((m) => ({ default: m.TestTransaction }))
);
const TestDataset = lazy(() =>
  import("@/pages/TestDataset").then((m) => ({ default: m.TestDataset }))
);
const RiskAnalysis = lazy(() =>
  import("@/pages/RiskAnalysis").then((m) => ({ default: m.RiskAnalysis }))
);
const AbuseRings = lazy(() =>
  import("@/pages/AbuseRings").then((m) => ({ default: m.AbuseRings }))
);
const Models = lazy(() => import("@/pages/Models").then((m) => ({ default: m.Models })));
const Training = lazy(() =>
  import("@/pages/Training").then((m) => ({ default: m.Training }))
);
const ApiDocs = lazy(() =>
  import("@/pages/ApiDocs").then((m) => ({ default: m.ApiDocs }))
);
const Sandbox = lazy(() =>
  import("@/pages/Sandbox").then((m) => ({ default: m.Sandbox }))
);
const ApiKeys = lazy(() =>
  import("@/pages/ApiKeys").then((m) => ({ default: m.ApiKeys }))
);
const Usage = lazy(() => import("@/pages/Usage").then((m) => ({ default: m.Usage })));
const Docs = lazy(() => import("@/pages/Docs").then((m) => ({ default: m.Docs })));
const Settings = lazy(() =>
  import("@/pages/Settings").then((m) => ({ default: m.Settings }))
);
const Login = lazy(() => import("@/pages/Login").then((m) => ({ default: m.Login })));

function NotFound() {
  return (
    <Card>
      <EmptyState
        icon={<Icon.Search size={26} />}
        title="That page does not exist"
        description="The link may be out of date. Everything Spark has is in the
          sidebar, or press Ctrl and K to search."
        action={
          <Link to="/">
            <Button variant="primary">Back to the overview</Button>
          </Link>
        }
      />
    </Card>
  );
}

export function AppRoutes() {
  const location = useLocation();
  return (
    <Routes location={location}>
      <Route path="/" element={<Overview />} />
      <Route path="/transaction" element={<TestTransaction />} />
      <Route path="/dataset" element={<TestDataset />} />
      <Route path="/analysis" element={<RiskAnalysis />} />
      <Route path="/rings" element={<AbuseRings />} />
      <Route path="/models" element={<Models />} />
      <Route path="/training" element={<Training />} />
      <Route path="/developers" element={<ApiDocs />} />
      <Route path="/sandbox" element={<Sandbox />} />
      <Route path="/keys" element={<ApiKeys />} />
      <Route path="/usage" element={<Usage />} />
      <Route path="/docs" element={<Docs />} />
      <Route path="/settings" element={<Settings />} />
      <Route path="/login" element={<Login />} />
      <Route path="/index.html" element={<Navigate to="/" replace />} />
      <Route path="*" element={<NotFound />} />
    </Routes>
  );
}
