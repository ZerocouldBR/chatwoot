# ServiceDesk M13: relatórios para quem tem reports >= readonly (ex.: Agente light no Zendesk).
class ReportPolicy < ApplicationPolicy
  def view?
    @account_user.administrator? || sd_access.at_least?('reports', 'readonly')
  end
end

ReportPolicy.prepend_mod_with('ReportPolicy')
