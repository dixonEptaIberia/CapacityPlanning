import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";
import type {
  CadenceOption,
  CellUpdate,
  CurrentUser,
  GridResponse,
  Plant,
  Version,
  VersionSnapshotResponse,
} from "../types";

export function usePlants() {
  return useQuery({
    queryKey: ["plants"],
    queryFn: async () => (await api.get<Plant[]>("/plants")).data,
  });
}

export function useCurrentUser() {
  return useQuery({
    queryKey: ["me"],
    queryFn: async () => (await api.get<CurrentUser>("/me")).data,
  });
}

export function useCadenceOptions() {
  return useQuery({
    queryKey: ["cadence-options"],
    queryFn: async () => (await api.get<CadenceOption[]>("/cadence-options")).data,
  });
}

export function useGrid(plantId: number | null, weeksCount = 8) {
  return useQuery({
    queryKey: ["grid", plantId, weeksCount],
    enabled: plantId != null,
    queryFn: async () =>
      (
        await api.get<GridResponse>(`/plants/${plantId}/grid`, {
          params: { weeks_count: weeksCount },
        })
      ).data,
  });
}

export function useOfficialVersions() {
  return useQuery({
    queryKey: ["versions", "official"],
    queryFn: async () => (await api.get<Version[]>("/versions/official")).data,
  });
}

export function useVersionSnapshot(versionId: number | null) {
  return useQuery({
    queryKey: ["version-snapshot", versionId],
    enabled: versionId != null,
    queryFn: async () =>
      (await api.get<VersionSnapshotResponse>(`/versions/${versionId}/snapshot`)).data,
  });
}

/** Download a version's tabular Excel export (respects dev auth via the api client). */
export async function downloadVersionExcel(versionId: number, versionName: string) {
  const res = await api.get(`/versions/${versionId}/export.xlsx`, {
    responseType: "blob",
  });
  const url = URL.createObjectURL(res.data as Blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `official_${versionName.replace(/\s+/g, "_")}_${versionId}.xlsx`;
  a.click();
  URL.revokeObjectURL(url);
}

export function useUpdateCell(plantId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (args: { lineId: number; week: string; update: CellUpdate }) =>
      (
        await api.put(
          `/plants/${plantId}/cells/${args.lineId}/${args.week}`,
          args.update,
        )
      ).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["grid", plantId] });
    },
  });
}
