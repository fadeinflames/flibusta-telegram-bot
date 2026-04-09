interface SkeletonCardProps {
  delay?: number
}

export default function SkeletonCard({ delay = 0 }: SkeletonCardProps) {
  return (
    <div className="flex gap-3.5 p-3.5" style={{ animationDelay: `${delay}ms` }}>
      <div
        className="w-[54px] h-[78px] flex-shrink-0 rounded-[10px] skeleton-shimmer"
        style={{ animationDelay: `${delay}ms` }}
      />
      <div className="flex-1 flex flex-col justify-center gap-2.5">
        <div
          className="h-[14px] w-[75%] rounded-[6px] skeleton-shimmer"
          style={{ animationDelay: `${delay + 60}ms` }}
        />
        <div
          className="h-[12px] w-[50%] rounded-[6px] skeleton-shimmer"
          style={{ animationDelay: `${delay + 120}ms` }}
        />
        <div
          className="h-[18px] w-[90px] rounded-full skeleton-shimmer mt-0.5"
          style={{ animationDelay: `${delay + 180}ms` }}
        />
      </div>
    </div>
  )
}
