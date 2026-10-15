# CCs do ticket (email_ccs do Zendesk) = atributo zd_cc da conversa, lista de e-mails separada por vírgula
# (formato da importação, docs/IMPORTACAO.md 4.1). As respostas públicas por e-mail levam esses endereços em cópia.
module ZendeskCompat::CcList
  ATTRIBUTE = 'zd_cc'.freeze
  EMAIL = /\A[^@\s,;<>]+@[^@\s,;<>]+\.[^@\s,;<>]+\z/

  module_function

  def parse(value)
    list = value.is_a?(Array) ? value : value.to_s.split(/[,;\s]+/)
    list.map { |email| email.to_s.strip.downcase.delete_prefix('<').delete_suffix('>') }.grep(EMAIL).uniq
  end

  def dump(emails)
    list = parse(emails)
    list.empty? ? nil : list.join(', ')
  end

  # email_ccs do Zendesk: [{user_email:|user_id:, action: 'put'|'delete'}] aplicados sobre a lista atual.
  def apply(current, changes, directory)
    list = parse(current)
    Array(changes).each do |change|
      change = change.to_h.with_indifferent_access
      email = change[:user_email].presence || email_for(change[:user_id], directory)
      next if email.blank?

      email = email.to_s.strip.downcase
      change[:action].to_s == 'delete' ? list.delete(email) : (list << email unless list.include?(email))
    end
    list
  end

  def email_for(user_id, directory)
    record = directory.actor(user_id)
    record.respond_to?(:email) ? record.email : nil
  end
end
