// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ModelSettings } from './ModelSettings'
import type { ProductModelSettings } from './api'

const mocks = vi.hoisted(() => ({ modelSettings: vi.fn(), saveModelSettings: vi.fn() }))
vi.mock('./api', () => ({ api: mocks }))
const fixture: ProductModelSettings = {
  providers: ['openai', 'anthropic', 'mistral', 'ollama'],
  credentials: { openai: 'configured', anthropic: 'missing', mistral: 'missing', ollama: 'not_required' },
  roles: Object.fromEntries(['coordinator', 'research', 'cheap_semantic'].map(name => [name, { provider: 'openai', model: '', enabled: false, reasoning_effort: null }])) as ProductModelSettings['roles'],
  status: { coordinator: 'missing', research: 'missing', cheap_semantic: 'missing' },
}
afterEach(cleanup)
beforeEach(() => { vi.clearAllMocks(); mocks.modelSettings.mockResolvedValue(fixture); mocks.saveModelSettings.mockResolvedValue(fixture) })
function mount() {
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><ModelSettings /></QueryClientProvider>)
}
it('shows three roles and markers, keeps credentials blank and saves only on demand', async () => {
  mount()
  await screen.findByLabelText('Coordinator API model')
  expect(screen.getByText('Research Agent · missing')).toBeTruthy()
  expect(screen.getByText('Cheap Semantic · missing')).toBeTruthy()
  expect((screen.getByLabelText('openai API key') as HTMLInputElement).value).toBe('')
  expect(mocks.saveModelSettings).not.toHaveBeenCalled()
  fireEvent.click(screen.getByLabelText('Coordinator enabled'))
  fireEvent.change(screen.getByLabelText('Coordinator API model'), { target: { value: 'fixture-coordinator' } })
  fireEvent.change(screen.getByLabelText('anthropic API key'), { target: { value: 'fake-only-test-key' } })
  fireEvent.click(screen.getByRole('button', { name: '保存 Models' }))
  await waitFor(() => expect(mocks.saveModelSettings).toHaveBeenCalledTimes(1))
  expect(mocks.saveModelSettings.mock.calls[0][0].roles.coordinator.model).toBe('fixture-coordinator')
  expect(mocks.saveModelSettings.mock.calls[0][0].credentials).toEqual({ anthropic: 'fake-only-test-key' })
  await waitFor(() => expect((screen.getByLabelText('anthropic API key') as HTMLInputElement).value).toBe(''))
})
it('preserves omitted keys and requires an explicit removal control', async () => {
  mount(); await screen.findByLabelText('openai API key')
  fireEvent.click(screen.getByRole('button', { name: '清除 openai key' }))
  fireEvent.click(screen.getByRole('button', { name: '保存 Models' }))
  await waitFor(() => expect(mocks.saveModelSettings).toHaveBeenCalledTimes(1))
  expect(mocks.saveModelSettings.mock.calls[0][0].credentials).toEqual({ openai: '' })
})
it('shows local schema errors and does not lose the edit on failed save', async () => {
  mocks.saveModelSettings.mockRejectedValue(new Error('Invalid model settings.'))
  mount(); await screen.findByLabelText('Coordinator API model')
  fireEvent.change(screen.getByLabelText('Coordinator API model'), { target: { value: 'invalid model' } })
  fireEvent.click(screen.getByRole('button', { name: '保存 Models' }))
  expect((await screen.findByRole('alert')).textContent).toContain('Invalid model settings')
  expect((screen.getByLabelText('Coordinator API model') as HTMLInputElement).value).toBe('invalid model')
})
