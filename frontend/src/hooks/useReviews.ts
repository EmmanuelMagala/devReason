import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { reviewsApi } from "@/api/reviews";
import type { ReviewCreate } from "@/types";

export function useReview(reviewId: string | null) {
  return useQuery({
    queryKey: ["review", reviewId],
    queryFn: () => reviewsApi.getOne(reviewId!),
    enabled: Boolean(reviewId),
    staleTime: 60_000,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "pending" || status === "running" ? 5_000 : false;
    },
  });
}

export function useCreateReview() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: ReviewCreate) => reviewsApi.create(payload),
    onSuccess: (result) => {
      void queryClient.invalidateQueries({ queryKey: ["review", result.id] });
    },
  });
}
