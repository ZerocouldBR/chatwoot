import type { Locator } from '@playwright/test';

// Picks an option in the app's own Select (components-next/select/Select.vue): open it, click the option by value.
export async function chooseOption(select: Locator, value: string) {
  await select.getByRole('combobox').click();
  await select.page().locator(`[role="listbox"] [data-value="${value}"]`).click();
}
