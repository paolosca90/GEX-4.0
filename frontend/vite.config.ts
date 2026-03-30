import * as reactPlugin from 'vite-plugin-react'
import type { UserConfig } from 'vite'

const config: UserConfig = {
  jsx: 'react',
  plugins: [reactPlugin],
  proxy: {
    '/api': 'http://localhost:8000',
    '/ws': { target: 'ws://localhost:8000', ws: true },
  }
}

export default config
