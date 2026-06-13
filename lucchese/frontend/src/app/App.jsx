// Root component (Rule 19/21). From App.jsx App() — selects the page by URL path.
import Providers from "./providers";
import { resolvePage } from "./routes";

export default function App() {
  const Page = resolvePage(window.location.pathname);
  return (
    <Providers>
      <Page />
    </Providers>
  );
}
