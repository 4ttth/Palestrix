import { LabView } from "./view";

export const metadata = { title: "Active lab" };

export default async function LabPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <LabView instanceId={id} />;
}
