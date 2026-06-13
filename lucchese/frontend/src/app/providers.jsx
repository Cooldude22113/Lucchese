// App-wide context providers (Rule 19). Currently a pass-through — page-level
// hooks own their state, so no global provider is required yet. Kept as the
// single place to add cross-cutting providers (errors, settings) when needed.
export default function Providers({ children }) {
  return children;
}
