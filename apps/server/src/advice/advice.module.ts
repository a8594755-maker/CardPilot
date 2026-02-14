import { Module } from '@nestjs/common';
import { AdviceService } from './advice.service';

@Module({
  providers: [AdviceService],
  exports: [AdviceService],
})
export class AdviceModule {}
