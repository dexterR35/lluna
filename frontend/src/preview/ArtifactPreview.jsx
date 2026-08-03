import { useEffect, useState } from "react";
import { Image as ImageIcon } from "lucide-react";
import { artifactObjectUrl } from "../api/client";
import { EmptyState, LoadingState } from "../components";
export function ArtifactPreview({ artifactId }) {
  const [state, setState] = useState({ url: null, error: null });
  useEffect(() => { let alive = true; let url; if (!artifactId) return undefined; setState({ url: null, error: null }); artifactObjectUrl(artifactId).then(value => { url = value; if (alive) setState({ url: value, error: null }); }).catch(error => alive && setState({ url: null, error: error.message })); return () => { alive = false; if (url) URL.revokeObjectURL(url); }; }, [artifactId]);
  if (!artifactId) return <EmptyState icon={<ImageIcon className="size-5" />} title="No preview yet" description="Run this node to create a local artifact preview." />;
  if (state.error) return <EmptyState title="Preview unavailable" description={state.error} />;
  if (!state.url) return <LoadingState label="Loading preview…" />;
  return <div className="checkerboard grid min-h-48 place-items-center overflow-auto rounded-lg border border-mg-border bg-mg-app p-2"><img src={state.url} alt="Node output preview" className="max-h-80 max-w-full object-contain" /></div>;
}
