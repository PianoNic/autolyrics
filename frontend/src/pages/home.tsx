import { App } from "@/App";
import { PageTitle } from "@/ui/page-title";
import { ClientOnly } from "@/ui/client-only";

const TITLE = "Editor ・ autolyrics";

const AppFallback: React.FC = () => (
  <div className="flex items-center justify-center h-screen bg-composer-bg text-composer-text-muted text-sm">
    Loading the editor
  </div>
);

const HomePage: React.FC = () => {
  return (
    <>
      <PageTitle title={TITLE} />
      <ClientOnly fallback={<AppFallback />}>
        <App />
      </ClientOnly>
    </>
  );
};

export default HomePage;
