# Reporting a security problem

Please use GitHub's private vulnerability reporting (the **Security** tab → "Report a
vulnerability") rather than a public issue.

`chatlens serve` runs a local server over conversations that usually contain customer data,
so these count:

- another web page, or a DNS-rebinding domain, reading traces or writing labels through the
  local server
- trace text that runs script or loads anything in the labelling page (the page has a
  hash-based CSP; a bypass counts)
- the server reading or writing files other than the traces and labels files it was given
- a request that makes the server hang or exhaust memory despite the size caps

The server binds to 127.0.0.1 and has no authentication. Exposing it on a network
yourself (a reverse proxy, port forwarding) is out of scope.

There is no bounty. I'll reply within a week.
