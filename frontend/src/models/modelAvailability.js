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
