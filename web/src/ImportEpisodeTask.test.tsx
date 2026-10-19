// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ImportEpisodeTask } from './ImportEpisodeTask'
import type { EpisodePreflight } from './api'

const mocks = vi.hoisted(() => ({ preflightEpisode: vi.fn(), commitEpisode: vi.fn(), hardScout: vi.fn() }))
vi.mock('./api', () => ({ api: mocks }))
const preview: EpisodePreflight = { filename: 'episode.md', size_bytes: 10, body: 'Source text', front_matter: {},
  target_id: 'CLAIM-0030', parse_summary: { claim: 2, proof: 1, evidence: 1, relation: 4 }, candidate_count: 8, content_sha256: 'digest' }
afterEach(cleanup)
beforeEach(() => { vi.clearAllMocks(); mocks.preflightEpisode.mockResolvedValue(preview); mocks.commitEpisode.mockResolvedValue({ episode: { episode_id: 'EPISODE-1' }, candidate_count: 8 }) })
function mount() {
  const onImported = vi.fn(); const onScout = vi.fn()
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { mutations: { retry: false } } })}>
    <ImportEpisodeTask problemId="PROBLEM-1" onImported={onImported} onScout={onScout} />
  </QueryClientProvider>)
  return { onImported, onScout }
}
function upload(name = 'episode.md') {
  const file = new File(['Source text'], name, { type: 'text/markdown' })
  fireEvent.change(screen.getByLabelText('Research Episode file'), { target: { files: [file] } }); return file
}
it('invalid Episode fails with zero import or Scout action', async () => {
  mocks.preflightEpisode.mockRejectedValue(new Error('No supported sections'))
  mount(); upload()
  expect(await screen.findByText(/未 Archive、未生成 Proposal/)).toBeTruthy()
  expect(screen.getByRole('alert').textContent).toContain('No supported sections')
  expect(mocks.commitEpisode).not.toHaveBeenCalled(); expect(mocks.hardScout).not.toHaveBeenCalled()
  expect(screen.queryByRole('button', { name: '确认导入并拆解' })).toBeNull()
})
it('previews counts and only commits the exact preflight file after Human confirmation', async () => {
  const { onImported, onScout } = mount(); const file = upload()
  await screen.findByText('已识别 Research Episode · episode.md')
  expect(screen.getByText('Explicit Relations: 4')).toBeTruthy()
  expect(mocks.commitEpisode).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: '确认导入并拆解' }))
  await waitFor(() => expect(mocks.commitEpisode).toHaveBeenCalledWith('PROBLEM-1', file, 'digest'))
  expect(await screen.findByText(/8 个 Proposals/)).toBeTruthy()
  expect(onImported).toHaveBeenCalledTimes(1)
  expect(mocks.hardScout).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: '运行 Scout' }))
  expect(onScout).toHaveBeenCalledTimes(1)
  expect(mocks.hardScout).not.toHaveBeenCalled() // Enters the separate confirmed Hard workflow.
})
it('ignores stale preflight responses after the user replaces the file or cancels', async () => {
  let resolveOld!: (value: EpisodePreflight) => void
  mocks.preflightEpisode.mockImplementationOnce(() => new Promise<EpisodePreflight>(resolve => { resolveOld = resolve }))
    .mockResolvedValueOnce({ ...preview, filename: 'new.md', content_sha256: 'new-digest' })
  mount(); upload('old.md'); upload('new.md')
  await screen.findByText('已识别 Research Episode · new.md')
  resolveOld({ ...preview, filename: 'old.md' })
  await waitFor(() => expect(screen.queryByText('已识别 Research Episode · old.md')).toBeNull())
  fireEvent.click(screen.getByRole('button', { name: '取消' }))
  expect(screen.queryByRole('button', { name: '确认导入并拆解' })).toBeNull()
  expect(mocks.commitEpisode).not.toHaveBeenCalled()
})
it('pastes Markdown through the same file preflight and digest commit, then shows parser facts', async () => {
  mocks.commitEpisode.mockResolvedValue({ episode: { episode_id: 'EPISODE-PASTED' }, candidate_count: 8,
    summary: { episode_id: 'EPISODE-PASTED', new_results: 2, new_gaps: 1, authority: 'provisional candidates' } })
  mount()
  fireEvent.change(screen.getByLabelText('Episode Markdown'), { target: { value: '## RESULT-1\nPasted body' } })
  expect(mocks.preflightEpisode).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'Preview Markdown' }))
  await screen.findByText('已识别 Research Episode · episode.md')
  expect(mocks.preflightEpisode.mock.calls[0][1].name).toBe('pasted-episode.md')
  const commit = screen.getByRole('button', { name: '确认导入并拆解' })
  fireEvent.click(commit); fireEvent.click(commit)
  await screen.findByText('New results')
  expect(mocks.commitEpisode).toHaveBeenCalledTimes(1)
  expect(screen.getByText('provisional candidates')).toBeTruthy()
})
it('editing pasted content invalidates an earlier preview', async () => {
  mount(); upload(); await screen.findByText('已识别 Research Episode · episode.md')
  fireEvent.change(screen.getByLabelText('Episode Markdown'), { target: { value: 'replacement' } })
  expect(screen.queryByRole('button', { name: '确认导入并拆解' })).toBeNull()
  expect(mocks.commitEpisode).not.toHaveBeenCalled()
})
