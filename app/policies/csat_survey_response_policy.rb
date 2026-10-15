# ServiceDesk M13: CSAT faz parte dos relatórios (reports >= readonly); download continua só do administrador.
class CsatSurveyResponsePolicy < ApplicationPolicy
  def index?
    @account_user.administrator? || sd_access.at_least?('reports', 'readonly')
  end

  def metrics?
    @account_user.administrator? || sd_access.at_least?('reports', 'readonly')
  end

  def download?
    @account_user.administrator?
  end
end

CsatSurveyResponsePolicy.prepend_mod_with('CsatSurveyResponsePolicy')
