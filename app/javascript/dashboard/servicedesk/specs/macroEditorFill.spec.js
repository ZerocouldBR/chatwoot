import {
  editorModeForFill,
  isFillForConversation,
  loadMacroFiles,
} from '../macroEditorFill';

describe('ServiceDesk macroEditorFill', () => {
  it('picks the editor mode from the fill', () => {
    expect(editorModeForFill({ isPrivate: true })).toBe('NOTE');
    expect(editorModeForFill({ isPrivate: false })).toBe('REPLY');
  });

  it('only fills the editor of the same conversation', () => {
    expect(isFillForConversation({ conversationId: '42' }, 42)).toBe(true);
    expect(isFillForConversation({ conversationId: 42 }, 43)).toBe(false);
    expect(isFillForConversation({ conversationId: 42 }, undefined)).toBe(
      false
    );
    expect(isFillForConversation(null, 42)).toBe(false);
  });

  it('downloads the macro attachments as files for the upload mixin', async () => {
    const fetchFn = vi.fn(async url => ({
      ok: url !== '/broken',
      blob: async () => new Blob(['abc'], { type: 'application/pdf' }),
    }));

    const loaded = await loadMacroFiles(
      [
        {
          file_url: '/ok',
          filename: 'tarifa.pdf',
          file_type: 'application/pdf',
        },
        { file_url: '/broken', filename: 'x.pdf' },
      ],
      fetchFn
    );

    expect(fetchFn).toHaveBeenCalledWith('/ok', { credentials: 'same-origin' });
    expect(loaded).toHaveLength(1);
    expect(loaded[0]).toMatchObject({
      name: 'tarifa.pdf',
      type: 'application/pdf',
      size: 3,
    });
    expect(loaded[0].file).toBeInstanceOf(File);
  });

  it('skips attachments that fail to download', async () => {
    const fetchFn = vi.fn().mockRejectedValue(new Error('offline'));

    expect(
      await loadMacroFiles([{ file_url: '/a', filename: 'a' }], fetchFn)
    ).toEqual([]);
  });
});
