// Centered overlay modal (Rule 19/20). Extracted from the fixed-overlay wrapper
// of App.jsx DocumentsPanel. Click-outside closes; inner clicks are stopped.
export default function Modal({ onClose, width = 500, children }) {
  return (
    <div
      style={{
        position: "fixed", inset: 0, background: "#000000aa",
        display: "flex", alignItems: "center", justifyContent: "center",
        zIndex: 100,
      }}
      onClick={onClose}
    >
      <div
        style={{
          background: "#0f0f0f", border: "1px solid #222",
          borderRadius: 16, width, maxHeight: "80vh",
          display: "flex", flexDirection: "column",
          overflow: "hidden",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {children}
      </div>
    </div>
  );
}
