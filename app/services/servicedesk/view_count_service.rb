# Conta os tickets de uma visualização com as mesmas regras do filtro da lista
# (Conversations::FilterService), incluindo as permissões de quem está logado.
class Servicedesk::ViewCountService < Conversations::FilterService
  def count
    return base_relation.count if @params[:payload].blank?

    validate_query_operator
    query_builder(@filters['conversations']).count
  end
end
