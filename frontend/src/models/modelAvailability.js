/** @param {import("../types").ParameterOption} option @param {import("../types").ModelInventory[]} models */
export function inventoryForOption(option, models) {
  return option.modelId ? models.find((model) => model.id === option.modelId) : undefined;
}

/** @param {import("../types").ParameterOption[]} options @param {import("../types").ModelInventory[]} models */
export function enabledModelOptions(options, models) {
  return options.filter((option) => {
    if (!option.modelId) return true;
    const inventory = inventoryForOption(option, models);
    return Boolean(inventory?.installed && inventory.enabled);
  });
}

/**
 * Resolve a node's saved model value against its option list, preferring the
 * enabled/installed subset but falling back to the full list so a model that
 * was disabled or uninstalled after being selected still resolves to its
 * real option (and capability contract) instead of `undefined`. Every UI
 * surface that needs "the currently selected model option" should go
 * through this so they stay consistent - see `enabledModelOptions`.
 * @param {import("../types").ParameterOption[]} allOptions
 * @param {import("../types").ParameterOption[]} enabledOptions
 * @param {unknown} value
 */
export function selectedModelOption(allOptions, enabledOptions, value) {
  return (
    enabledOptions.find((option) => String(option.value) === String(value)) ||
    allOptions.find((option) => String(option.value) === String(value))
  );
}
