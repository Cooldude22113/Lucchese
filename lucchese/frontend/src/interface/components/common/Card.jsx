// Hover-elevating surface card (Rule 19/20). From Home.jsx Card.
import { useState } from "react";
import { surface, border } from "../../../utils/theme";

export default function Card({ children, style = {}, onClick }) {
  const [hovered, setHovered] = useState(false);
  return (
    <div
      onClick={onClick}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        background: surface,
        border: `1px solid ${hovered && onClick ? "#c8a96e44" : border}`,
        borderRadius: 14,
        padding: "1.4rem",
        transition: "all 0.2s ease",
        cursor: onClick ? "pointer" : "default",
        transform: hovered && onClick ? "translateY(-2px)" : "none",
        boxShadow: hovered && onClick ? "0 8px 32px #c8a96e0a" : "none",
        ...style,
      }}
    >
      {children}
    </div>
  );
}
