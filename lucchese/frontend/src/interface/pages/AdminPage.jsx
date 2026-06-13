// Admin screen (Rule 19/20). From AdminPanel.jsx — page chrome around the
// AdminPanel body.
import PageHeader from "../layout/PageHeader";
import AdminPanel from "../components/admin/AdminPanel";

export default function AdminPage() {
  return (
    <div style={{ maxWidth: 1100, margin: "0 auto", padding: "2rem 1.5rem" }}>
      <PageHeader subtitle="Memory Admin" />
      <AdminPanel />
    </div>
  );
}
