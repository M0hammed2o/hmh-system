import client from "./client";

export interface Site {
  id: string;
  project_id: string;
  name: string;
  code: string | null;
  site_type: string;
  location_description: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface SiteCreate {
  name: string;
  code?: string | null;
  site_type?: string;
  location_description?: string | null;
}

export interface SiteUpdate {
  name?: string;
  code?: string | null;
  site_type?: string;
  location_description?: string | null;
  is_active?: boolean;
}

export const sitesApi = {
  list: async (projectId: string, includeInactive = false): Promise<Site[]> => {
    const res = await client.get<{ data: Site[] }>(
      `/projects/${projectId}/sites/`,
      { params: includeInactive ? { include_inactive: true } : {} }
    );
    return res.data.data;
  },

  get: async (siteId: string): Promise<Site> => {
    const res = await client.get<{ data: Site }>(`/sites/${siteId}`);
    return res.data.data;
  },

  create: async (projectId: string, body: SiteCreate): Promise<Site> => {
    const res = await client.post<{ data: Site }>(
      `/projects/${projectId}/sites/`,
      body
    );
    return res.data.data;
  },

  update: async (siteId: string, body: SiteUpdate): Promise<Site> => {
    const res = await client.patch<{ data: Site }>(`/sites/${siteId}`, body);
    return res.data.data;
  },
};
