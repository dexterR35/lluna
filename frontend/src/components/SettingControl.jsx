import { NumberField } from "./NumberField";
import { Select } from "./Select";
import { Switch } from "./Switch";
import { TextField } from "./TextField";

/**
 * Single typed settings control. Styling comes from shared field primitives.
 * @param {{
 *   label: string,
 *   hint?: string,
 *   value: unknown,
 *   choices?: (string|number)[],
 *   onCommit: (value: unknown) => void,
 *   onDraft?: (value: unknown) => void,
 * }} props
 */
export function SettingControl({
  label,
  hint,
  value,
  choices,
  onCommit,
  onDraft,
}) {
  if (typeof value === "boolean") {
    return (
      <div className="ui-stack-xs">
        <Switch
          label={label}
          checked={Boolean(value)}
          onChange={(next) => onCommit(next)}
        />
        {hint && <p className="ui-help">{hint}</p>}
      </div>
    );
  }

  if (choices?.length) {
    return (
      <Select
        label={label}
        hint={hint}
        value={String(value)}
        options={choices.map((choice) => ({
          value: String(choice),
          label: String(choice)
            .replaceAll("_", " ")
            .replaceAll("-", " ")
            .replace(/\b\w/g, (match) => match.toUpperCase()),
        }))}
        onChange={(event) => onCommit(event.target.value)}
      />
    );
  }

  if (typeof value === "number") {
    return (
      <NumberField
        label={label}
        hint={hint}
        value={value}
        onChange={(event) => onDraft?.(Number(event.target.value))}
        onBlur={(event) => onCommit(Number(event.target.value))}
      />
    );
  }

  return (
    <TextField
      label={label}
      hint={hint}
      value={String(value ?? "")}
      onChange={(event) => onDraft?.(event.target.value)}
      onBlur={(event) => onCommit(event.target.value)}
    />
  );
}
