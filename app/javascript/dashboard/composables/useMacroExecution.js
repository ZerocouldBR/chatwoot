import { ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { useAlert, useTrack } from 'dashboard/composables';
import { useStore, useMapGetter } from 'dashboard/composables/store';
import { useConversationRequiredAttributes } from 'dashboard/composables/useConversationRequiredAttributes';
import { CONVERSATION_EVENTS } from 'dashboard/helper/AnalyticsHelper/events';
import { BUS_EVENTS } from 'shared/constants/busEvents';
import { emitter } from 'shared/helpers/mitt';
import ticketFormsMeta from 'dashboard/servicedesk/ticketFormsMeta.json';

// change_status is not offered by the macro builder, but the API accepts it and
// it resolves the conversation just like resolve_conversation does. Its param is
// stored as raw JSON, so the status can be the enum name or its integer value.
const RESOLVED_STATUSES = ['resolved', 1];

// ServiceDesk: set_ticket_status resolves when the label maps to the native
// `resolved` status (ticketFormsMeta.json, same table as ticket_statuses.yml).
const normalizeLabel = label =>
  String(label || '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .trim()
    .toLowerCase();
const nativeForTicketStatus = label => {
  const statuses = ticketFormsMeta.statuses || {};
  if (statuses[label]) return statuses[label].native;
  const key = Object.keys(statuses).find(
    name => normalizeLabel(name) === normalizeLabel(label)
  );
  return key ? statuses[key].native : undefined;
};
const resolvesTicketStatus = label =>
  nativeForTicketStatus(label) === 'resolved';

export const resolvesConversation = macro =>
  macro.actions.some(
    ({ action_name: name, action_params: params }) =>
      name === 'resolve_conversation' ||
      (name === 'change_status' && RESOLVED_STATUSES.includes(params?.[0])) ||
      (name === 'set_ticket_status' && resolvesTicketStatus(params?.[0]))
  );

/**
 * ServiceDesk M5.1 (macro_fill_editor): what the macro puts in the reply editor
 * instead of sending. The backend skips the same actions (Macros::ExecutionService):
 * send_message and send_attachment always; add_private_note only when the macro has
 * no public reply, because the editor holds one mode at a time.
 *
 * @returns {{isPrivate: boolean, content: string, files: Array}|null}
 */
export const getEditorFill = macro => {
  if (!macro?.fill_editor) return null;

  const actions = macro.actions || [];
  const textsOf = name =>
    actions
      .filter(action => action.action_name === name)
      .map(action => action.action_params?.[0])
      .filter(Boolean);
  const replies = textsOf('send_message');
  const notes = textsOf('add_private_note');
  const blobIds = actions
    .filter(action => action.action_name === 'send_attachment')
    .flatMap(action => action.action_params || []);
  const files = (macro.files || []).filter(file =>
    blobIds.includes(file.blob_id)
  );

  if (!replies.length && !notes.length && !files.length) return null;

  const isPrivate = !replies.length && notes.length > 0;
  return {
    isPrivate,
    content: (isPrivate ? notes : replies).join('\n\n'),
    files,
  };
};

const EDITOR_ACTIONS = ['send_message', 'send_attachment'];

/** Whether anything is left for the backend once the editor got its part. */
export const hasActionsToExecute = macro => {
  const fill = getEditorFill(macro);
  if (!fill) return macro.actions.length > 0;

  return macro.actions.some(
    ({ action_name: name }) =>
      !EDITOR_ACTIONS.includes(name) &&
      !(name === 'add_private_note' && fill.isPrivate)
  );
};

/**
 * Runs a macro against a conversation, holding back the ones that resolve it until
 * the required custom attributes are filled in.
 *
 * `execute` returns the attributes to prompt for when the caller has to open the
 * modal first, and null once the macro has been handed off.
 */
export function useMacroExecution() {
  const store = useStore();
  const { t } = useI18n();
  const { checkMissingAttributes } = useConversationRequiredAttributes();

  const conversationById = useMapGetter('getConversationById');

  const executingMacroId = ref(null);
  const pendingExecution = ref(null);

  const customAttributesFor = conversationId =>
    conversationById.value(conversationId)?.custom_attributes || {};

  const successMessage = (skippedResolve, filledEditor) => {
    if (filledEditor) {
      return skippedResolve
        ? t('MACROS.EXECUTE.FILLED_EDITOR_WITHOUT_RESOLVING')
        : t('MACROS.EXECUTE.FILLED_EDITOR');
    }
    return skippedResolve
      ? t('MACROS.EXECUTE.EXECUTED_WITHOUT_RESOLVING')
      : t('MACROS.EXECUTE.EXECUTED_SUCCESSFULLY');
  };

  const runMacro = async (
    { macro, conversationId },
    skippedResolve = false
  ) => {
    const fill = getEditorFill(macro);
    if (fill) {
      emitter.emit(BUS_EVENTS.SD_MACRO_FILL_EDITOR, {
        conversationId,
        ...fill,
      });
    }

    try {
      executingMacroId.value = macro.id;
      if (hasActionsToExecute(macro)) {
        await store.dispatch('macros/execute', {
          macroId: macro.id,
          conversationIds: [conversationId],
        });
      }
      useTrack(CONVERSATION_EVENTS.EXECUTED_A_MACRO);
      useAlert(successMessage(skippedResolve, !!fill));
    } catch (error) {
      useAlert(t('MACROS.ERROR'));
    } finally {
      executingMacroId.value = null;
    }
  };

  const execute = (macro, conversationId) => {
    const execution = { macro, conversationId };

    if (!resolvesConversation(macro)) {
      runMacro(execution);
      return null;
    }

    const customAttributes = customAttributesFor(conversationId);
    const { hasMissing, missing } = checkMissingAttributes(customAttributes);
    if (!hasMissing) {
      runMacro(execution);
      return null;
    }

    pendingExecution.value = execution;
    return { missing, customAttributes };
  };

  const submitPendingAttributes = async ({ attributes }) => {
    const execution = pendingExecution.value;
    pendingExecution.value = null;

    try {
      await store.dispatch('updateCustomAttributes', {
        conversationId: execution.conversationId,
        customAttributes: {
          ...customAttributesFor(execution.conversationId),
          ...attributes,
        },
      });
    } catch (error) {
      useAlert(t('CUSTOM_ATTRIBUTES.FORM.UPDATE.ERROR'));
      return;
    }

    runMacro(execution);
  };

  // Dismissing the modal still runs the macro, the backend leaves the
  // conversation unresolved while the required attributes are empty.
  const dismissPendingAttributes = () => {
    if (!pendingExecution.value) return;

    runMacro(pendingExecution.value, true);
    pendingExecution.value = null;
  };

  return {
    executingMacroId,
    execute,
    submitPendingAttributes,
    dismissPendingAttributes,
  };
}
