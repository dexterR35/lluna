import { useEffect, useMemo } from "react";
import {
  Box,
  Cpu,
  Image,
  Monitor,
  Moon,
  RotateCcw,
  Settings2,
  Sparkles,
  Subtitles,
  Wand2,
} from "lucide-react";
import {
  ActionRow,
  CompactButton,
  Dialog,
  NavItem,
  SectionHeader,
  Switch,
} from "../components";
import { useDesktopStore } from "../state/desktopStore";
import { useServerStore } from "../state/serverStore";
import { PREFERENCE_SECTIONS } from "./fieldMeta";
import { ModelsPanel } from "./ModelsPanel";
import { SettingsForm } from "./SettingsForm";

/** @type {Record<string, import("react").ComponentType<{className?: string}>>} */
const SECTION_ICONS = {
  editor: Monitor,
  runtime: Cpu,
  subtitle: Subtitles,
  background_removal: Image,
  enhancement: Sparkles,
  low_light: Moon,
  generation: Wand2,
  object_selection: Box,
  models: Box,
};

/** @param {{section: string, values: Record<string, any>}} props */
function PreferenceSection({ section, values }) {
  const reset = useServerStore((store) => store.resetSettings);
  return (
    <div className="ui-stack">
      <SettingsForm section={section} values={values} />
      <div className="ui-settings-footer">
        <CompactButton onClick={() => void reset(section)}>
          <RotateCcw className="ui-icon-sm" /> Reset section
        </CompactButton>
      </div>
    </div>
  );
}

/** @param {{onReset: () => void}} props */
function EditorSettings({ onReset }) {
  const minimapVisible = useDesktopStore((store) => store.minimapVisible);
  const set = useDesktopStore((store) => store.setValue);
  return (
    <div className="ui-stack">
      <Switch
        label="Show minimap"
        checked={minimapVisible}
        onChange={(value) => set("minimapVisible", value)}
      />
      <ActionRow
        title="Reset workspace layout"
        description="Restore panel sizes and visibility."
        action={
          <CompactButton variant="secondary" onClick={onReset}>
            Reset
          </CompactButton>
        }
      />
    </div>
  );
}

export function SettingsDialog() {
  const open = useDesktopStore((store) => store.settingsOpen);
  const modelsOpen = useDesktopStore((store) => store.modelsOpen);
  const sectionId = useDesktopStore((store) => store.settingsSection);
  const set = useDesktopStore((store) => store.setValue);
  const settings = useServerStore((store) => store.settings);
  const isOpen = open || modelsOpen;

  useEffect(() => {
    if (modelsOpen && !open) {
      set("settingsOpen", true);
      set("settingsSection", "models");
      set("modelsOpen", false);
    }
  }, [modelsOpen, open, set]);

  const sections = useMemo(() => {
    const byId = Object.fromEntries(
      Object.entries(settings || {}).filter(
        ([key, value]) =>
          key !== "schema_version" &&
          value !== null &&
          typeof value === "object",
      ),
    );
    return PREFERENCE_SECTIONS.map((item) => ({
      ...item,
      values:
        item.id === "editor"
          ? null
          : /** @type {Record<string, any> | null} */ (byId[item.id] || null),
    })).filter((item) => item.id === "editor" || item.values);
  }, [settings]);

  const active =
    sectionId === "models"
      ? {
          id: "models",
          label: "Models",
          description: null,
          values: null,
        }
      : sections.find((section) => section.id === sectionId) ||
        sections[0] || {
          id: "editor",
          label: "Editor",
          description: "Canvas appearance and workspace behavior.",
          values: null,
        };

  function close() {
    set("settingsOpen", false);
    set("modelsOpen", false);
  }

  return (
    <Dialog
      open={isOpen}
      onClose={close}
      title="Settings"
      description="Preferences and local model management"
      wide
      className="ui-dialog-wide"
      bodyClassName="!max-h-none !overflow-hidden !p-0"
    >
      <div className="ui-settings">
        <nav aria-label="Settings sections" className="ui-settings-nav">
          <p className="ui-kicker">Preferences</p>
          {sections.map((section) => {
            const Icon = SECTION_ICONS[section.id] || Settings2;
            return (
              <NavItem
                key={section.id}
                active={active.id === section.id}
                icon={<Icon />}
                onClick={() => set("settingsSection", section.id)}
              >
                {section.label}
              </NavItem>
            );
          })}
          <div className="ui-rule my-2.5" />
          <p className="ui-kicker">Models</p>
          <NavItem
            active={active.id === "models"}
            icon={<Box />}
            onClick={() => set("settingsSection", "models")}
          >
            Models
          </NavItem>
        </nav>
        <section className="ui-settings-main">
          <SectionHeader
            title={active.label}
            description={
              active.id === "models"
                ? undefined
                : active.description || undefined
            }
          />
          {active.id === "models" ? (
            <ModelsPanel />
          ) : active.id === "editor" || !active.values ? (
            <EditorSettings onReset={() => useDesktopStore.getState().reset()} />
          ) : (
            <PreferenceSection
              key={active.id}
              section={active.id}
              values={active.values}
            />
          )}
        </section>
      </div>
    </Dialog>
  );
}
