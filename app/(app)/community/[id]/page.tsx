import { WriteupView } from "./view";

export const metadata = { title: "Writeup" };

export default async function WriteupPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <WriteupView id={id} />;
}
