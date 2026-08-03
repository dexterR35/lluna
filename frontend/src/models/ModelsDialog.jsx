import { Box, Download, Trash2 } from "lucide-react";
import { api } from "../api/client";
import { Badge, Button, Card, Dialog, EmptyState, Switch } from "../components";
import { useDesktopStore } from "../state/desktopStore";
import { useServerStore } from "../state/serverStore";

export function ModelsDialog() {
  const open = useDesktopStore((store) => store.modelsOpen);
  const set = useDesktopStore((store) => store.setValue);
  const models = useServerStore((store) => store.models);
  const setLifecycleState = useServerStore(
    (store) => store.setModelLifecycleState,
  );

  async function confirmState(
    /** @type {string} */ modelId,
    /** @type {(model: import("../types").ModelInventory) => boolean} */ matches,
  ) {
    for (const delay of [150, 350, 750, 1500, 3000]) {
      await new Promise((resolve) => setTimeout(resolve, delay));
      /** @type {import("../types").ModelInventory[]} */
      let inventory;
      try {
        inventory = await api("/api/models");
      } catch {
        return;
      }
      const model = inventory.find((item) => item.id === modelId);
      if (model && matches(model)) {
        useServerStore.setState({ models: inventory });
        return;
      }
    }
  }

  async function action(
    /** @type {import("../types").ModelInventory} */ model,
    /** @type {"install"|"enable"|"disable"|"remove"} */ operation,
  ) {
    await api(
      `/api/models/${model.id}${operation === "remove" ? "" : `/${operation}`}`,
      { method: operation === "remove" ? "DELETE" : "POST" },
    );
    if (operation === "enable") {
      setLifecycleState(model.id, { enabled: true });
      void confirmState(model.id, (item) => item.installed && item.enabled);
    } else if (operation === "disable") {
      setLifecycleState(model.id, { enabled: false });
      void confirmState(model.id, (item) => !item.enabled);
    } else if (operation === "remove") {
      setLifecycleState(model.id, {
        installed: false,
        enabled: false,
        state: "not_installed",
      });
      void confirmState(model.id, (item) => !item.installed);
    } else {
      void confirmState(model.id, (item) => item.installed);
    }
  }
  return (
    <Dialog
      open={open}
      onClose={() => set("modelsOpen", false)}
      title="Local model manager"
      description="Models remain on this device. Review each license before use."
    >
      <div className="grid gap-3">
        {models.length ? (
          models.map((model) => (
            <Card key={model.id} as="article" className="p-4">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h3 className="text-[13px] font-semibold tracking-tight">
                    {model.display_name || model.id}
                  </h3>
                  <p className="mt-1 text-[11px] text-mg-secondary">
                    {model.purpose || "Local inference"} ·{" "}
                    {model.license || "See upstream license"}
                  </p>
                </div>
                <Badge
                  tone={
                    model.installed
                      ? model.enabled
                        ? "success"
                        : "warning"
                      : "neutral"
                  }
                >
                  {model.installed
                    ? model.enabled
                      ? "Enabled"
                      : "Disabled"
                    : "Not installed"}
                </Badge>
              </div>
              <Card className="mt-3 bg-mg-app/50 px-3 py-1" padded={false}>
                <Switch
                  label="Show in node model selectors"
                  checked={Boolean(model.installed && model.enabled)}
                  disabled={!model.installed || !model.can_toggle}
                  onChange={(enabled) =>
                    void action(model, enabled ? "enable" : "disable")
                  }
                />
              </Card>
              <div className="mt-3 flex flex-wrap gap-2">
                {!model.installed && model.can_install && (
                  <Button onClick={() => void action(model, "install")}>
                    <Download className="size-4" />
                    Install
                  </Button>
                )}
                {!model.installed && !model.can_install && (
                  <Badge tone="neutral">
                    Provided by application installation
                  </Badge>
                )}
                {model.installed && model.can_uninstall && (
                  <Button
                    variant="danger"
                    onClick={() => void action(model, "remove")}
                  >
                    <Trash2 className="size-4" />
                    Uninstall
                  </Button>
                )}
              </div>
            </Card>
          ))
        ) : (
          <EmptyState
            icon={<Box className="size-5" />}
            title="No model catalog available"
          />
        )}
      </div>
    </Dialog>
  );
}
