# ServiceDesk B2B: lista os segmentos de usuário do portal para o seletor "Visível para" do editor de artigo.
# Os segmentos vêm do Zendesk (provisioning/import_help_center.rb); a edição fica para uma próxima etapa.
class Api::V1::Accounts::PortalUserSegmentsController < Api::V1::Accounts::BaseController
  before_action :portal
  before_action -> { check_authorization(Article) }

  def index
    @segments = @portal.user_segments.order(:user_type, :name)
  end

  private

  def portal
    @portal ||= Current.account.portals.find_by!(slug: params[:portal_id])
  end
end
