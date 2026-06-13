// Inline doc-marker → download button (Rule 19/20). From App.jsx Message.
// If the assistant text contains a [GENERATE_DOC: …] marker, offer the doc.
import { extractDocTitle, stripDocMarker } from "../../../utils/docMarker";
import DownloadDocButton from "../documents/DownloadDocButton";

export default function DocumentMarker({ content }) {
  const title = extractDocTitle(content);
  if (!title) return null;
  return <DownloadDocButton content={stripDocMarker(content)} title={title} />;
}
