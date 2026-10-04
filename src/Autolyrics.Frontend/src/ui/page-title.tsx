import { Head } from "vite-react-ssg";

// -- Component ----------------------------------------------------------------

// The document title for a page. autolyrics runs locally, so there are no indexing, social or
// analytics tags to manage.
const PageTitle: React.FC<{ title: string }> = ({ title }) => (
  <Head>
    <title>{title}</title>
  </Head>
);

// -- Exports ------------------------------------------------------------------

export { PageTitle };
