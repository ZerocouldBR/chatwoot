import { flushPromises } from '@vue/test-utils';
import { useAlert, useTrack } from 'dashboard/composables';
import { useMapGetter, useStore } from 'dashboard/composables/store';
import { useConversationRequiredAttributes } from 'dashboard/composables/useConversationRequiredAttributes';
import { emitter } from 'shared/helpers/mitt';
import { BUS_EVENTS } from 'shared/constants/busEvents';
import {
  getEditorFill,
  hasActionsToExecute,
  resolvesConversation,
  useMacroExecution,
} from '../useMacroExecution';

vi.mock('dashboard/composables/store');
vi.mock('dashboard/composables');
vi.mock('dashboard/composables/useConversationRequiredAttributes');
vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: key => key }),
}));

const CONVERSATION_ID = 42;

const addLabel = { action_name: 'add_label', action_params: ['spam'] };
const resolveConversation = {
  action_name: 'resolve_conversation',
  action_params: [],
};

const macroWith = actions => ({ id: 7, name: 'Test macro', actions });

const dispatch = vi.fn();
const checkMissingAttributes = vi.fn();

const mockConversation = (customAttributes = {}) => {
  useMapGetter.mockImplementation(getter =>
    getter === 'getConversationById'
      ? { value: () => ({ custom_attributes: customAttributes }) }
      : { value: null }
  );
};

describe('useMacroExecution', () => {
  beforeEach(() => {
    dispatch.mockReset().mockResolvedValue(undefined);
    checkMissingAttributes.mockReset().mockReturnValue({
      hasMissing: false,
      missing: [],
    });
    useAlert.mockClear();
    useTrack.mockClear();

    useStore.mockReturnValue({ dispatch });
    useConversationRequiredAttributes.mockReturnValue({
      checkMissingAttributes,
    });
    mockConversation();
  });

  it('runs a macro that cannot resolve the conversation straight away', async () => {
    const { execute } = useMacroExecution();

    const pending = execute(macroWith([addLabel]), CONVERSATION_ID);
    await flushPromises();

    expect(pending).toBeNull();
    expect(checkMissingAttributes).not.toHaveBeenCalled();
    expect(dispatch).toHaveBeenCalledWith('macros/execute', {
      macroId: 7,
      conversationIds: [CONVERSATION_ID],
    });
    expect(useAlert).toHaveBeenCalledWith(
      'MACROS.EXECUTE.EXECUTED_SUCCESSFULLY'
    );
  });

  it('runs a resolving macro when no required attributes are missing', async () => {
    const { execute } = useMacroExecution();

    const pending = execute(macroWith([resolveConversation]), CONVERSATION_ID);
    await flushPromises();

    expect(pending).toBeNull();
    expect(checkMissingAttributes).toHaveBeenCalled();
    expect(dispatch).toHaveBeenCalledWith('macros/execute', expect.anything());
  });

  it('holds back a resolving macro and reports the missing attributes', async () => {
    checkMissingAttributes.mockReturnValue({
      hasMissing: true,
      missing: ['priority'],
    });
    mockConversation({ category: 'sales' });

    const { execute } = useMacroExecution();

    const pending = execute(macroWith([resolveConversation]), CONVERSATION_ID);
    await flushPromises();

    expect(pending).toEqual({
      missing: ['priority'],
      customAttributes: { category: 'sales' },
    });
    expect(dispatch).not.toHaveBeenCalled();
  });

  it.each([['resolved'], [1]])(
    'treats change_status %s as resolving the conversation',
    async status => {
      checkMissingAttributes.mockReturnValue({
        hasMissing: true,
        missing: ['priority'],
      });

      const { execute } = useMacroExecution();
      const macro = macroWith([
        { action_name: 'change_status', action_params: [status] },
      ]);

      expect(execute(macro, CONVERSATION_ID)).not.toBeNull();
      await flushPromises();
      expect(dispatch).not.toHaveBeenCalled();
    }
  );

  it('does not treat change_status open as resolving the conversation', async () => {
    checkMissingAttributes.mockReturnValue({
      hasMissing: true,
      missing: ['priority'],
    });

    const { execute } = useMacroExecution();
    const macro = macroWith([
      { action_name: 'change_status', action_params: ['open'] },
    ]);

    expect(execute(macro, CONVERSATION_ID)).toBeNull();
    await flushPromises();
    expect(dispatch).toHaveBeenCalledWith('macros/execute', expect.anything());
  });

  it('saves the submitted attributes before running the pending macro', async () => {
    checkMissingAttributes.mockReturnValue({
      hasMissing: true,
      missing: ['priority'],
    });
    mockConversation({ category: 'sales' });

    const { execute, submitPendingAttributes } = useMacroExecution();
    execute(macroWith([resolveConversation]), CONVERSATION_ID);
    await submitPendingAttributes({ attributes: { priority: 'high' } });
    await flushPromises();

    expect(dispatch).toHaveBeenNthCalledWith(1, 'updateCustomAttributes', {
      conversationId: CONVERSATION_ID,
      customAttributes: { category: 'sales', priority: 'high' },
    });
    expect(dispatch).toHaveBeenNthCalledWith(2, 'macros/execute', {
      macroId: 7,
      conversationIds: [CONVERSATION_ID],
    });
  });

  it('does not run the macro when saving the attributes fails', async () => {
    checkMissingAttributes.mockReturnValue({
      hasMissing: true,
      missing: ['priority'],
    });
    dispatch.mockRejectedValueOnce(new Error('nope'));

    const { execute, submitPendingAttributes } = useMacroExecution();
    execute(macroWith([resolveConversation]), CONVERSATION_ID);
    await submitPendingAttributes({ attributes: { priority: 'high' } });
    await flushPromises();

    expect(dispatch).toHaveBeenCalledTimes(1);
    expect(useAlert).toHaveBeenCalledWith(
      'CUSTOM_ATTRIBUTES.FORM.UPDATE.ERROR'
    );
  });

  it('still runs the macro when the prompt is dismissed', async () => {
    checkMissingAttributes.mockReturnValue({
      hasMissing: true,
      missing: ['priority'],
    });

    const { execute, dismissPendingAttributes } = useMacroExecution();
    execute(macroWith([resolveConversation]), CONVERSATION_ID);
    dismissPendingAttributes();
    await flushPromises();

    expect(dispatch).toHaveBeenCalledWith('macros/execute', expect.anything());
    expect(useAlert).toHaveBeenCalledWith(
      'MACROS.EXECUTE.EXECUTED_WITHOUT_RESOLVING'
    );
  });

  it('ignores a dismissal when nothing is pending', async () => {
    const { dismissPendingAttributes } = useMacroExecution();

    dismissPendingAttributes();
    await flushPromises();

    expect(dispatch).not.toHaveBeenCalled();
  });

  it('alerts when the macro fails to run', async () => {
    dispatch.mockRejectedValueOnce(new Error('boom'));

    const { execute, executingMacroId } = useMacroExecution();
    execute(macroWith([addLabel]), CONVERSATION_ID);
    await flushPromises();

    expect(useAlert).toHaveBeenCalledWith('MACROS.ERROR');
    expect(executingMacroId.value).toBeNull();
  });

  describe('ServiceDesk: macro preenche o editor (fill_editor)', () => {
    const reply = { action_name: 'send_message', action_params: ['Olá!'] };
    const note = { action_name: 'add_private_note', action_params: ['Nota'] };
    const ticketStatus = {
      action_name: 'set_ticket_status',
      action_params: ['Desenvolvimento'],
    };
    const fillMacro = (actions, extra = {}) => ({
      ...macroWith(actions),
      fill_editor: true,
      ...extra,
    });
    let emitSpy;

    beforeEach(() => {
      emitSpy = vi.spyOn(emitter, 'emit');
    });

    afterEach(() => {
      emitSpy.mockRestore();
    });

    it('fills the editor with the reply and runs the other actions', async () => {
      const { execute } = useMacroExecution();

      execute(fillMacro([reply, addLabel, ticketStatus]), CONVERSATION_ID);
      await flushPromises();

      expect(emitSpy).toHaveBeenCalledWith(BUS_EVENTS.SD_MACRO_FILL_EDITOR, {
        conversationId: CONVERSATION_ID,
        isPrivate: false,
        content: 'Olá!',
        files: [],
      });
      expect(dispatch).toHaveBeenCalledWith('macros/execute', {
        macroId: 7,
        conversationIds: [CONVERSATION_ID],
      });
      expect(useAlert).toHaveBeenCalledWith('MACROS.EXECUTE.FILLED_EDITOR');
    });

    it('does not call the backend when the macro only has the reply', async () => {
      const { execute } = useMacroExecution();

      execute(fillMacro([reply]), CONVERSATION_ID);
      await flushPromises();

      expect(emitSpy).toHaveBeenCalledWith(
        BUS_EVENTS.SD_MACRO_FILL_EDITOR,
        expect.objectContaining({ content: 'Olá!' })
      );
      expect(dispatch).not.toHaveBeenCalled();
    });

    it('keeps the upstream flow when fill_editor is off', async () => {
      const { execute } = useMacroExecution();

      execute(macroWith([reply]), CONVERSATION_ID);
      await flushPromises();

      expect(emitSpy).not.toHaveBeenCalledWith(
        BUS_EVENTS.SD_MACRO_FILL_EDITOR,
        expect.anything()
      );
      expect(dispatch).toHaveBeenCalledWith(
        'macros/execute',
        expect.anything()
      );
    });

    it('holds a set_ticket_status that resolves until required attributes are filled', async () => {
      checkMissingAttributes.mockReturnValue({
        hasMissing: true,
        missing: ['priority'],
      });
      const { execute } = useMacroExecution();
      const resolving = fillMacro([
        reply,
        { action_name: 'set_ticket_status', action_params: ['Concluído'] },
      ]);

      expect(execute(resolving, CONVERSATION_ID)).not.toBeNull();
      await flushPromises();
      expect(emitSpy).not.toHaveBeenCalledWith(
        BUS_EVENTS.SD_MACRO_FILL_EDITOR,
        expect.anything()
      );
      expect(dispatch).not.toHaveBeenCalled();
    });

    it('treats only solved/closed labels as resolving', () => {
      expect(resolvesConversation(macroWith([ticketStatus]))).toBe(false);
      expect(
        resolvesConversation(
          macroWith([
            { action_name: 'set_ticket_status', action_params: ['Resolvido'] },
          ])
        )
      ).toBe(true);
    });

    describe('getEditorFill', () => {
      it('uses the private note when there is no public reply', () => {
        expect(getEditorFill(fillMacro([note, addLabel]))).toEqual({
          isPrivate: true,
          content: 'Nota',
          files: [],
        });
      });

      it('prefers the public reply and joins several replies', () => {
        const second = { action_name: 'send_message', action_params: ['Até'] };

        expect(getEditorFill(fillMacro([reply, note, second]))).toEqual({
          isPrivate: false,
          content: 'Olá!\n\nAté',
          files: [],
        });
      });

      it('brings the macro attachments to the editor', () => {
        const file = { blob_id: 9, filename: 'a.pdf', file_url: '/a.pdf' };
        const macro = fillMacro(
          [{ action_name: 'send_attachment', action_params: [9] }],
          { files: [file, { blob_id: 10, filename: 'b.pdf' }] }
        );

        expect(getEditorFill(macro)).toEqual({
          isPrivate: false,
          content: '',
          files: [file],
        });
      });

      it('returns null without fill_editor or without text', () => {
        expect(getEditorFill(macroWith([reply]))).toBeNull();
        expect(getEditorFill(fillMacro([addLabel]))).toBeNull();
      });
    });

    describe('hasActionsToExecute', () => {
      it('ignores the actions that went to the editor', () => {
        expect(hasActionsToExecute(fillMacro([reply]))).toBe(false);
        expect(hasActionsToExecute(fillMacro([note]))).toBe(false);
        expect(hasActionsToExecute(fillMacro([reply, note]))).toBe(true);
        expect(hasActionsToExecute(fillMacro([reply, ticketStatus]))).toBe(
          true
        );
        expect(hasActionsToExecute(macroWith([reply]))).toBe(true);
      });
    });
  });
});
