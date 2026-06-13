// Inline error text (Rule 15/19). The repeated "⚠ {error}" red lines used by
// Chat and Voice for audio/network failures.
export default function ErrorMessage({ children, style = {} }) {
  if (!children) return null;
  return (
    <p style={{
      fontSize: "0.78rem", color: "#e06c75", lineHeight: 1.6, ...style,
    }}>
      ⚠ {children}
    </p>
  );
}
