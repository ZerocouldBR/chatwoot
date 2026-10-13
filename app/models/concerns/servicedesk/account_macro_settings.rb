# Configuração da conta `macro_fill_editor` (M5.1): quando ligada, aplicar uma macro PREENCHE o editor com a
# resposta/nota (e os anexos) para o agente revisar e enviar; as demais ações continuam sendo aplicadas na hora.
# Sem valor na conta, vale o padrão da instalação: ENV SD_MACRO_FILL_EDITOR (padrão true no ServiceDesk).
module Servicedesk::AccountMacroSettings
  extend ActiveSupport::Concern

  included do
    store_accessor :settings, :macro_fill_editor
    before_validation :normalize_macro_fill_editor
    validates :macro_fill_editor, inclusion: { in: [true, false] }, allow_nil: true
  end

  class_methods do
    def macro_fill_editor_default?
      ActiveModel::Type::Boolean.new.cast(ENV.fetch('SD_MACRO_FILL_EDITOR', 'true')) != false
    end
  end

  def macro_fill_editor?
    return self.class.macro_fill_editor_default? if macro_fill_editor.nil?

    macro_fill_editor == true
  end

  private

  # A API pode mandar "true"/"false" (form) em vez de booleano.
  def normalize_macro_fill_editor
    case macro_fill_editor.to_s
    when 'true', '1' then self.macro_fill_editor = true
    when 'false', '0' then self.macro_fill_editor = false
    when '' then self.macro_fill_editor = nil
    end
  end
end
