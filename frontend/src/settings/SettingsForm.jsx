import { useEffect, useMemo, useState } from "react";
import { SettingControl } from "../components/SettingControl";
import { useServerStore } from "../state/serverStore";
import { FIELD_META, titleCase } from "./fieldMeta";

/**
 * Renders and persists a settings section (or a subset of keys).
 * @param {{
 *   section: string,
 *   values: Record<string, any>,
 *   keys?: string[],
 * }} props
 */
export function SettingsForm({ section, values, keys }) {
  const update = useServerStore((store) => store.updateSettings);
  const keyList = keys?.join("|") ?? "";
  const entries = useMemo(() => {
    const source = keyList
      ? keyList
          .split("|")
          .filter((key) => key in values)
          .map((key) => [key, values[key]])
      : Object.entries(values);
    return source.filter(([key]) => {
      const meta = FIELD_META[`${section}.${key}`] || FIELD_META[key];
      return !meta?.hide;
    });
  }, [keyList, section, values]);

  const [draft, setDraft] = useState(() => Object.fromEntries(entries));
  useEffect(() => {
    setDraft(Object.fromEntries(entries));
  }, [entries]);

  async function commit(/** @type {string} */ key, /** @type {unknown} */ value) {
    setDraft((/** @type {Record<string, any>} */ current) => ({ ...current, [key]: value }));
    await update({ [section]: { ...values, ...draft, [key]: value } });
  }

  return (
    <div className={keys ? "ui-stack-sm" : "ui-stack"}>
      {entries.map(([key]) => {
        const meta = FIELD_META[`${section}.${key}`] || FIELD_META[key];
        return (
          <SettingControl
            key={key}
            label={meta?.label || titleCase(key)}
            hint={meta?.description}
            value={draft[key]}
            choices={meta?.choices}
            onDraft={(value) =>
              setDraft((/** @type {Record<string, any>} */ current) => ({ ...current, [key]: value }))
            }
            onCommit={(value) => void commit(key, value)}
          />
        );
      })}
    </div>
  );
}
