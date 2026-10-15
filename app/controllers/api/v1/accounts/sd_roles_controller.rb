# ServiceDesk M13: API dos papéis (tela Configurações > Papéis).
#   GET    /api/v1/accounts/:account_id/sd_roles          -> papéis + catálogo de permissões
#   GET    /api/v1/accounts/:account_id/sd_roles/me      -> papel e permissões efetivas do usuário atual
#   GET    /api/v1/accounts/:account_id/sd_roles/:id
#   POST   /api/v1/accounts/:account_id/sd_roles          { sd_role: { name, key?, description, base_role, permissions } }
#   PATCH  /api/v1/accounts/:account_id/sd_roles/:id
#   DELETE /api/v1/accounts/:account_id/sd_roles/:id      (papel de sistema ou em uso não pode ser excluído)
class Api::V1::Accounts::SdRolesController < Api::V1::Accounts::BaseController
  before_action :fetch_role, only: [:show, :update, :destroy]
  before_action :check_authorization

  def index
    @sd_roles = Current.account.sd_roles.ordered.to_a
    @member_counts = Current.account.account_users.where.not(sd_role_id: nil).group(:sd_role_id).count
  end

  def show; end

  def me; end

  def create
    @sd_role = Current.account.sd_roles.new(role_params)
    @sd_role.key = unique_key(@sd_role.key.presence || @sd_role.name)
    @sd_role.position = (Current.account.sd_roles.maximum(:position) || 0) + 1
    @sd_role.save!
    render :show
  end

  def update
    attrs = role_params
    attrs = attrs.except(:key, :base_role) if @sd_role.system?
    @sd_role.update!(attrs)
    render :show
  end

  def destroy
    return render_could_not_create_error('Papel padrão do Zendesk não pode ser excluído') if @sd_role.system?
    return render_could_not_create_error('Papel em uso por agentes: troque o papel deles antes') if @sd_role.account_users.exists?

    @sd_role.destroy!
    head :ok
  end

  private

  def fetch_role
    @sd_role = Current.account.sd_roles.find(params[:id])
  end

  def check_authorization
    authorize(@sd_role || SdRole)
  end

  def role_params
    permitted = params.require(:sd_role).permit(:name, :key, :description, :base_role)
    permissions = params[:sd_role][:permissions]
    permitted[:permissions] = permissions.respond_to?(:permit) ? permissions.permit!.to_h : permissions if permissions
    permitted
  end

  def unique_key(source)
    base = I18n.transliterate(source.to_s).downcase.gsub(/[^a-z0-9]+/, '_').gsub(/\A_+|_+\z/, '')
    base = "papel_#{base}" unless base.match?(/\A[a-z]/)
    base = base[0, 40]
    key = base
    index = 1
    while Current.account.sd_roles.exists?(key: key)
      index += 1
      key = "#{base}_#{index}"
    end
    key
  end
end
