# Tags do Zendesk <-> etiquetas do ServiceDesk, com a mesma normalização da importação (docs/IMPORTACAO.md 4.2):
# minúsculas; letras, números, "_" e "-"; outros caracteres viram "_"; sem "_"/"-" no início; curtas ganham "tag_".
module ZendeskCompat::Tags
  module_function

  def normalize(tags)
    list = tags.is_a?(String) ? tags.split(/[\s,]+/) : Array(tags)
    list.filter_map { |tag| normalize_one(tag) }.uniq
  end

  def normalize_one(tag)
    value = tag.to_s.strip.downcase.gsub(/[^\p{L}\p{N}_-]/, '_').sub(/\A[_-]+/, '')
    return if value.empty?

    value.length < 2 ? "tag_#{value}" : value
  end
end
