import axios from 'axios';
import * as types from '../../../mutation-types';
import { actions } from '../../customViews';

const commit = vi.fn();
global.axios = axios;
vi.mock('axios');

beforeEach(() => {
  axios.get.mockReset();
  commit.mockClear();
});

// ServiceDesk: views do Zendesk compartilhadas (API servicedesk/views)
describe('#get conversation views (ServiceDesk shared views)', () => {
  it('uses the shared views visible to the user, with columns and sort', async () => {
    const view = {
      id: 9,
      name: 'Meu grupo',
      shared: true,
      member: true,
      position: 2,
      columns: [{ id: 'subject', titulo: 'Assunto' }],
      sort: { campo: 'updated', ordem: 'desc' },
      query: { payload: [] },
    };
    axios.get.mockResolvedValue({ data: { payload: [view] } });
    await actions.get({ commit }, 'conversation');
    expect(axios.get.mock.calls[0][0]).toContain('servicedesk/views');
    expect(commit.mock.calls[1]).toEqual([
      types.default.SET_CUSTOM_VIEW,
      {
        data: [{ ...view, filter_type: 'conversation' }],
        filterType: 'conversation',
      },
    ]);
  });

  it('falls back to the user filters when the API is not there', async () => {
    axios.get
      .mockRejectedValueOnce({ response: { status: 404 } })
      .mockResolvedValueOnce({ data: [{ id: 1, name: 'Pessoal' }] });
    await actions.get({ commit }, 'conversation');
    expect(commit.mock.calls[1]).toEqual([
      types.default.SET_CUSTOM_VIEW,
      { data: [{ id: 1, name: 'Pessoal' }], filterType: 'conversation' },
    ]);
  });

  it('keeps contact segments on the native API', async () => {
    axios.get.mockResolvedValue({ data: [{ id: 3 }] });
    await actions.get({ commit }, 'contact');
    expect(axios.get).toHaveBeenCalledTimes(1);
    expect(axios.get.mock.calls[0][0]).toContain('custom_filters');
  });
});
