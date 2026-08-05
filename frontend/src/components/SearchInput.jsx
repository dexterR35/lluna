import { Search, X } from "../icons";
import { IconButton } from "./IconButton";

/** @param {{value: string, onChange: (value: string) => void, placeholder?: string, label?: string, autoFocus?: boolean}} props */
export function SearchInput({
  value,
  onChange,
  placeholder = "Search…",
  label = "Search",
  autoFocus = false,
}) {
  return (
    <label className="ui-search">
      <Search aria-hidden className="ui-icon text-mg-muted" />
      <span className="sr-only">{label}</span>
      <input
        autoFocus={autoFocus}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
      />
      {value && (
        <IconButton
          label="Clear search"
          className="size-5 rounded-md"
          onClick={() => onChange("")}
        >
          <X className="ui-icon-sm" />
        </IconButton>
      )}
    </label>
  );
}
