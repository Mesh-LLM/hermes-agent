import { setupMockBackend, waitForAppReady } from './fixtures'
import { expect, test } from './test'

test('Mesh LLM settings shows client controls and model state', async () => {
  const fixture = await setupMockBackend()

  try {
    await waitForAppReady(fixture, 120_000)
    const page = fixture.page
    await page.getByRole('button', { name: 'Open settings', exact: true }).click()
    await page.getByRole('button', { name: 'Providers', exact: true }).click()
    await page.getByRole('button', { name: 'Mesh LLM', exact: true }).click()

    await expect(page.getByText('Mesh LLM client')).toBeVisible()
    await expect(page.getByText('Available models')).toBeVisible()
    await expect(page.getByRole('button', { name: 'Start', exact: true })).toBeDisabled()
    await expect(page.getByRole('button', { name: 'Stop', exact: true })).toBeDisabled()
    await expect(page.getByRole('button', { name: 'Restart', exact: true })).toBeDisabled()
    await page.screenshot({ path: test.info().outputPath('meshllm-settings.png') })

    await page.getByRole('button', { name: 'Accounts', exact: true }).click()
    await page.getByRole('button', { name: 'Other providers', exact: true }).click()
    await page.getByRole('button', { name: /Mesh LLM/ }).last().click()
    await expect(page.getByText('Public network')).toBeVisible()
    await page.screenshot({ path: test.info().outputPath('meshllm-public-connect.png') })
    await page.getByText('Private network').click()
    await expect(page.getByPlaceholder('Paste invite token')).toBeVisible()
    await page.screenshot({ path: test.info().outputPath('meshllm-private-connect.png') })
  } finally {
    await fixture.cleanup()
  }
})
