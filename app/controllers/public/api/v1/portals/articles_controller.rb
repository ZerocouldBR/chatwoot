class Public::Api::V1::Portals::ArticlesController < Public::Api::V1::Portals::BaseController
  before_action :ensure_custom_domain_request, only: [:show, :index, :show_markdown]
  before_action :portal
  before_action :set_portal_layout
  before_action :set_view_variant
  before_action :ensure_portal_feature_enabled
  before_action :enforce_portal_sign_in, except: [:tracking_pixel]
  before_action :set_category, except: [:index, :show, :tracking_pixel]
  before_action :set_article, only: [:show, :show_markdown]
  before_action :authorize_article_access, only: [:show, :show_markdown]
  layout 'portal'

  def index
    @search_query = list_params[:query]
    @articles = @portal.articles.published.visible_to_segments(portal_visible_segment_ids).includes(:category, :author)

    @articles = @articles.where(locale: permitted_params[:locale]) if permitted_params[:locale].present?

    @articles_count = @articles.count

    search_articles
    order_by_sort_param
    limit_results
  end

  def show
    @og_image_url = helpers.set_og_image_url(@portal.name, @article.title)
    @parsed_content = render_article_content(@article.content.to_s)
  end

  def show_markdown
    return head :not_found unless @article&.published?

    render plain: @article.content.to_s, content_type: 'text/markdown; charset=utf-8'
  end

  def tracking_pixel
    @article = @portal.articles.find_by(slug: permitted_params[:article_slug])
    return head :not_found unless @article

    @article.increment_view_count if @article.published?

    # Serve the 1x1 tracking pixel with 24-hour private cache
    # Private cache bypasses CDN but allows browser caching to prevent duplicate views from same user
    expires_in 24.hours, public: false
    response.headers['Content-Type'] = 'image/png'

    pixel_path = Rails.public_path.join('assets/images/tracking-pixel.png')
    send_file pixel_path, type: 'image/png', disposition: 'inline'
  end

  private

  def limit_results
    return if list_params[:per_page].blank?

    per_page = [list_params[:per_page].to_i, 100].min
    per_page = 25 if per_page < 1
    @articles = @articles.page(list_params[:page]).per(per_page)
  end

  def search_articles
    @articles = @articles.search(list_params) if list_params.present?
  end

  def order_by_sort_param
    @articles = if list_params[:sort].present? && list_params[:sort] == 'views'
                  @articles.order_by_views
                else
                  @articles.order_by_position
                end
  end

  def set_article
    @article = @portal.articles.find_by(slug: permitted_params[:article_slug])
  end

  # ServiceDesk B2B: no portal do cliente (customer_portal.enabled) rascunho só abre com o token de
  # pré-visualização do painel (no Chatwoot original o rascunho abre para quem souber o slug); artigo restrito a
  # um segmento só abre para o contato logado que pertence ao segmento (anônimo vai para o login).
  def authorize_article_access
    return article_not_found if @article.blank?
    return if article_preview_token_valid?
    return article_not_found if customer_portal_enabled? && !@article.published?
    return if article_visible_to_viewer?
    return article_not_found unless login_may_unlock_article?

    redirect_to portal_customer_login_path(@portal.slug, portal_customer_locale, return_to: request.fullpath)
  end

  def article_not_found
    action_name == 'show_markdown' ? head(:not_found) : render_404
  end

  def article_visible_to_viewer?
    @article.portal_user_segment_id.blank? || portal_visible_segment_ids.include?(@article.portal_user_segment_id)
  end

  # Anônimo no portal do cliente vai para o login; logado sem permissão, markdown ou portal sem login: 404.
  def login_may_unlock_article?
    customer_portal_enabled? && !portal_contact_signed_in? && action_name != 'show_markdown'
  end

  def article_preview_token_valid?
    token = params[:preview_token].presence
    return false if token.blank?

    Rails.application.message_verifier(:sd_article_preview).verified(token, purpose: :preview) == @article.id
  end

  def set_category
    return if permitted_params[:category_slug].blank?

    @category = @portal.categories.find_by!(
      slug: permitted_params[:category_slug],
      locale: permitted_params[:locale]
    )
  end

  def list_params
    @list_params ||= params.permit(:query, :locale, :sort, :status, :page, :per_page).tap do |permitted|
      permitted[:query] = permitted[:query].to_s.strip.presence
    end
  end

  def permitted_params
    params.permit(:slug, :category_slug, :locale, :id, :article_slug)
  end

  def render_article_content(content)
    ChatwootMarkdownRenderer.new(content).render_article
  end
end

Public::Api::V1::Portals::ArticlesController.prepend_mod_with('Public::Api::V1::Portals::ArticlesController')
