import ConversionDemo from "../components/ConversionDemo.jsx";
import ProjectHeader from "../components/ProjectHeader.jsx";

export default function Home() {
  return (
    <main className="app-shell">
      <ProjectHeader />
      <ConversionDemo />
    </main>
  );
}
