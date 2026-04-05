#include <tunables/global>

profile sandbox-default flags=(attach_disconnected,mediate_deleted) {
  #include <abstractions/base>

  file,
  deny network,
  deny mount,
  deny ptrace,
  deny signal,
  deny /proc/** rwklx,
  deny /sys/** rwklx,
}
