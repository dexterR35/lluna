import { LoaderCircle } from "../icons";
/** @param {{label?: string}} props */
export function LoadingState({label="Loading…"}){return <div role="status" className="flex min-h-32 items-center justify-center gap-2 text-sm text-mg-secondary"><LoaderCircle aria-hidden className="size-5 animate-spin text-mg-running"/><span>{label}</span></div>}
