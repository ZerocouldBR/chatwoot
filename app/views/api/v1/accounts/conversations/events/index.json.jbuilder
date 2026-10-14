json.payload @events do |event|
  json.id event.id
  json.event_type event.event_type
  json.field_name event.field_name
  json.previous_value event.previous_value
  json.value event.value
  labels = @labels[event.field_name]
  if labels
    json.previous_value_label labels[event.previous_value]
    json.value_label labels[event.value]
  end
  json.via event.via
  json.author do
    json.type event.author_type
    json.id event.author_id
    json.name event.author.try(:available_name) || event.author.try(:name) || event.author.try(:title)
  end
  json.created_at event.created_at.to_i
end
