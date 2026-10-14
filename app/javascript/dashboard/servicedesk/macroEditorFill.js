/**
 * ServiceDesk M5.1: a macro preenche o editor (resposta ou nota) para o agente revisar.
 * O ReplyBox escuta BUS_EVENTS.SD_MACRO_FILL_EDITOR (emitido por useMacroExecution)
 * e usa estas funções para o texto e para os anexos da macro.
 */
import { REPLY_EDITOR_MODES } from 'dashboard/components/widgets/WootWriter/constants';

export const editorModeForFill = ({ isPrivate }) =>
  isPrivate ? REPLY_EDITOR_MODES.NOTE : REPLY_EDITOR_MODES.REPLY;

export const isFillForConversation = (fill, conversationId) =>
  !!fill &&
  conversationId !== undefined &&
  conversationId !== null &&
  String(fill.conversationId) === String(conversationId);

/**
 * Baixa os anexos da macro (`macro.files`) e devolve no formato que o
 * fileUploadMixin espera (`{ name, type, size, file }`). Anexo que falhar fica de
 * fora; o chamador compara os tamanhos para avisar o agente.
 */
export const loadMacroFiles = async (files = [], fetchFn = fetch) => {
  const loaded = await Promise.all(
    files.map(async macroFile => {
      try {
        const response = await fetchFn(macroFile.file_url, {
          credentials: 'same-origin',
        });
        if (!response.ok) return null;

        const blob = await response.blob();
        const file = new File([blob], macroFile.filename, {
          type: macroFile.file_type || blob.type,
        });
        return { name: file.name, type: file.type, size: file.size, file };
      } catch (error) {
        return null;
      }
    })
  );
  return loaded.filter(Boolean);
};
