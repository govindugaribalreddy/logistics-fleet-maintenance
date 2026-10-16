import { useEffect, useState } from "react";
import { getHealth } from "../services/api";

export function HealthPage() {
  const [status, setStatus] = useState("checking");
  useEffect(() => { getHealth().then((data) => setStatus(data.status)).catch(() => setStatus("unavailable")); }, []);
  return <main><h1>Logistics Fleet Maintenance</h1><p>API status: <strong>{status}</strong></p></main>;
}
