export const ATTRIBUTE_KEY_REQUIRED = 'ATTRIBUTE_KEY_REQUIRED';
export const FILTER_OPERATOR_REQUIRED = 'FILTER_OPERATOR_REQUIRED';
export const VALUE_REQUIRED = 'VALUE_REQUIRED';
export const VALUE_MUST_BE_BETWEEN_1_AND_998 =
  'VALUE_MUST_BE_BETWEEN_1_AND_998';
export const ACTION_PARAMETERS_REQUIRED = 'ACTION_PARAMETERS_REQUIRED';
export const ATLEAST_ONE_ACTION_REQUIRED = 'ATLEAST_ONE_ACTION_REQUIRED';

export const isEmptyValue = value => {
  if (value === null || value === undefined || value === '') {
    return true;
  }

  if (Array.isArray(value)) {
    return !value.length;
  }

  // We can safely check the type here as both the null value
  // and the array is ruled out earlier.
  if (typeof value === 'object') {
    return !Object.keys(value).length;
  }

  return false;
};
// ------------------------------------------------------------------
// ------------------------ Filter Validation -----------------------
// ------------------------------------------------------------------

/**
 * Validates a single filter for conversations or contacts.
 *
 * @param {Object} filter - The filter object to validate.
 * @param {string} filter.attribute_key - The key of the attribute to filter on.
 * @param {string} filter.filter_operator - The operator to use for filtering.
 * @param {string|number|Array} [filter.values] - The value(s) to filter by (required for most operators).
 *
 * @returns {string|null} An error message if validation fails, or null if validation passes.
 */
export const validateSingleFilter = filter => {
  if (!filter.attribute_key) {
    return ATTRIBUTE_KEY_REQUIRED;
  }

  if (!filter.filter_operator) {
    return FILTER_OPERATOR_REQUIRED;
  }

  const operatorRequiresValue = !['is_present', 'is_not_present'].includes(
    filter.filter_operator
  );

  if (operatorRequiresValue && isEmptyValue(filter.values)) {
    return VALUE_REQUIRED;
  }

  if (
    filter.filter_operator === 'days_before' &&
    (parseInt(filter.values, 10) <= 0 || parseInt(filter.values, 10) >= 999)
  ) {
    return VALUE_MUST_BE_BETWEEN_1_AND_998;
  }

  return null;
};

const isFilterCondition = filter =>
  !!filter && typeof filter === 'object' && !validateSingleFilter(filter);

/**
 * Parses conversation filters handed over through the `filters` URL query
 * (see the report drilldown "View all").
 *
 * @param {string} serializedFilters - JSON list of filter conditions.
 * @returns {Array|null} The conditions, or null when the value is not a non-empty list of valid conditions.
 */
export const parseRouteFilters = serializedFilters => {
  let filters;
  try {
    filters = JSON.parse(serializedFilters);
  } catch {
    return null;
  }

  return Array.isArray(filters) &&
    filters.length > 0 &&
    filters.every(isFilterCondition)
    ? filters
    : null;
};

// ------------------------------------------------------------------
// ------------------------ Action Validation -----------------------
// ------------------------------------------------------------------

/**
 * Validates a single action of an automation object.
 *
 * @param {Object} action - The action to validate.
 * @returns {string|null} An error message if validation fails, or null if validation passes.
 */
const validateSingleAction = action => {
  const noParamActions = [
    'mute_conversation',
    'snooze_conversation',
    'resolve_conversation',
    'remove_assigned_agent',
    'remove_assigned_team',
    'open_conversation',
    'pending_conversation',
  ];

  if (
    !noParamActions.includes(action.action_name) &&
    (!action.action_params || action.action_params.length === 0)
  ) {
    return ACTION_PARAMETERS_REQUIRED;
  }

  // ServiceDesk: set_custom_attribute precisa do atributo (valor vazio limpa o campo)
  if (
    action.action_name === 'set_custom_attribute' &&
    (!Array.isArray(action.action_params) || !action.action_params[0])
  ) {
    return ACTION_PARAMETERS_REQUIRED;
  }

  return null;
};

/**
 * Validates the actions of an automation object.
 *
 * @param {Array} actions - The actions to validate.
 * @returns {Object} An object containing any validation errors.
 */
export const validateActions = actions => {
  if (!actions || actions.length === 0) {
    return { actions: ATLEAST_ONE_ACTION_REQUIRED };
  }

  return actions.reduce((errors, action, index) => {
    const error = validateSingleAction(action);
    if (error) {
      errors[`action_${index}`] = error;
    }
    return errors;
  }, {});
};
