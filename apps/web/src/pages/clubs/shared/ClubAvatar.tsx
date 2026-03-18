export function ClubAvatar({
  name,
  color,
  size = 'md',
}: {
  name: string;
  color: string | null;
  size?: 'sm' | 'md' | 'lg';
}) {
  const sizes = {
    sm: 'h-10 w-10 text-lg rounded-xl',
    md: 'h-14 w-14 text-xl rounded-2xl sm:h-16 sm:w-16',
    lg: 'h-20 w-20 text-2xl rounded-2xl',
  };
  return (
    <div
      className={`flex items-center justify-center font-bold text-white shadow-lg shadow-black/40 ${sizes[size]}`}
      style={{ backgroundColor: color ?? '#6366f1' }}
    >
      {name[0]?.toUpperCase()}
    </div>
  );
}
