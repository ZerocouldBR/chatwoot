json.payload do
  json.array! @segments do |segment|
    json.id segment.id
    json.name segment.name
    json.user_type segment.user_type
    json.company_ids segment.company_ids
    json.tags segment.tags
    json.or_tags segment.or_tags
    json.articles_count segment.articles.count
  end
end
