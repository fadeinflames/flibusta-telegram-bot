interface SkeletonCardProps {
  delay?: number
}

export default function SkeletonCard({ delay = 0 }: SkeletonCardProps) {
  const stagger = delay * 80

  return (
    <div
      className="flex gap-3.5 p-3"
      style={{
        opacity: 0,
        animation: `skeleton-fade-in 0.3s ease-out ${stagger}ms forwards`,
      }}
    >
      {/* Cover skeleton */}
      <div
        className="w-[56px] h-[80px] flex-shrink-0 rounded-xl skeleton-shimmer"
        style={{ animationDelay: `${stagger}ms` }}
      />

      {/* Text skeletons */}
      <div className="flex-1 flex flex-col justify-center gap-2.5 py-0.5">
        <div
          className="h-[15px] w-[70%] rounded-lg skeleton-shimmer"
          style={{ animationDelay: `${stagger + 80}ms` }}
        />
        <div
          className="h-[13px] w-[45%] rounded-lg skeleton-shimmer"
          style={{ animationDelay: `${stagger + 160}ms` }}
        />
        <div
          className="h-[20px] w-[80px] rounded-full skeleton-shimmer mt-0.5"
          style={{ animationDelay: `${stagger + 240}ms` }}
        />
      </div>
    </div>
  )
}
