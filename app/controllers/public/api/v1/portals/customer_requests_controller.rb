# ServiceDesk B2B: "Minhas solicitações", "Solicitações da organização", "Enviar uma solicitação" e o
# detalhe do ticket para o usuário final, como no Zendesk Guide. Exige contato logado no portal.
class Public::Api::V1::Portals::CustomerRequestsController < Public::Api::V1::Portals::BaseController
  before_action :ensure_custom_domain_request
  before_action :portal
  before_action :set_portal_layout
  before_action :set_view_variant
  before_action :ensure_portal_feature_enabled
  before_action :ensure_customer_portal_enabled!
  before_action :require_portal_contact!
  before_action :verify_authenticity_token, only: [:create, :reply]
  before_action :set_request, only: [:show, :reply]
  layout 'portal'

  def index
    @scope = params[:scope] == 'organization' && finder.organization_enabled? ? 'organization' : 'mine'
    @status_filter = params[:status].presence_in(PortalCustomers::RequestStatus::GROUPS)
    @query = params[:query].to_s.strip.first(100)
    relation = @scope == 'organization' ? finder.organization : finder.mine
    @requests = finder.search(relation, query: @query, status: @status_filter, page: params[:page])
    @organization_enabled = finder.organization_enabled?
  end

  def show
    load_request_details
  end

  def new
    load_forms
  end

  def create
    conversation = PortalCustomers::CreateRequestService.new(
      portal: @portal, contact: portal_contact, form_id: params[:form_id], subject: params[:subject],
      description: params[:description], fields: params[:fields] || {}, attachments: params[:attachments]
    ).perform
    redirect_to portal_customer_request_path(@portal.slug, @locale, conversation.display_id, created: 1)
  rescue PortalCustomers::CreateRequestService::Error => e
    @errors = e.messages
    load_forms
    render :new, status: :unprocessable_entity
  end

  def reply
    unless finder.can_reply?(@conversation)
      @errors = [I18n.t('public_portal.sd.requests.errors.reply_not_allowed')]
      load_request_details
      return render(:show, status: :forbidden)
    end

    target = PortalCustomers::ReplyService.new(conversation: @conversation, contact: portal_contact, content: params[:content],
                                               attachments: params[:attachments], solve: params[:solve] == '1').perform
    # resposta a ticket fechado: o cliente vai para o acompanhamento criado
    extra = target.id == @conversation.id ? {} : { created: 1 }
    redirect_to portal_customer_request_path(@portal.slug, @locale, target.display_id, **extra)
  rescue PortalCustomers::CreateRequestService::Error => e
    @errors = e.messages
    load_request_details
    render :show, status: :unprocessable_entity
  end

  private

  def finder
    @finder ||= PortalCustomers::RequestsFinder.new(portal: @portal, contact: portal_contact)
  end

  def set_request
    @conversation = finder.find(params[:display_id])
    render_404 if @conversation.blank?
  end

  def load_forms
    forms = PortalCustomers::RequestForms.new(portal: @portal)
    @forms = forms.all
    @form = forms.find(params[:form_id].presence || params[:form])
  end

  def load_request_details
    @status = PortalCustomers::RequestStatus.new(@conversation)
    @can_reply = finder.can_reply?(@conversation)
    @messages = @conversation.messages
                             .where(private: false, message_type: %i[incoming outgoing])
                             .where.not(content_type: 'input_csat')
                             .includes(:attachments, :sender)
                             .reorder(created_at: :asc, id: :asc)
                             .select { |message| message.content.present? || message.attachments.any? }
    @csat_url = "/survey/responses/#{@conversation.uuid}" if @conversation.messages.exists?(content_type: 'input_csat')
  end
end
