// Empty-state placeholder text (Rule 19/20). Consolidates the repeated
// "No conversations / No documents / Nothing yet" blocks across the monoliths.
export default function EmptyState({ children, style = {} }) {
  return (
    <p style={{
      color: "#333", fontSize: "0.78rem", textAlign: "center",
      padding: "1rem 0", ...style,
    }}>
      {children}
    </p>
  );
}
